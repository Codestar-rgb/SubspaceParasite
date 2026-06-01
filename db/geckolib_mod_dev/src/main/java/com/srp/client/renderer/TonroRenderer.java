package com.srp.client.renderer;

import com.srp.client.model.TonroModel;
import com.srp.entity.TonroEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class TonroRenderer extends GeoEntityRenderer<TonroEntity> {

    public TonroRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new TonroModel());
    }
}
