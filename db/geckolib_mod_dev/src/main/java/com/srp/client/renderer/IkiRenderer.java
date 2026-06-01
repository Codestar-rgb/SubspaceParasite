package com.srp.client.renderer;

import com.srp.client.model.IkiModel;
import com.srp.entity.IkiEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class IkiRenderer extends GeoEntityRenderer<IkiEntity> {

    public IkiRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new IkiModel());
    }
}
