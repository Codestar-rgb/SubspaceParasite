package com.srp.client.renderer;

import com.srp.client.model.MudoModel;
import com.srp.entity.MudoEntity;
import software.bernie.geckolib.renderer.GeoEntityRenderer;
import net.minecraft.client.renderer.entity.EntityRendererProvider;

public class MudoRenderer extends GeoEntityRenderer<MudoEntity> {

    public MudoRenderer(EntityRendererProvider.Context renderManager) {
        super(renderManager, new MudoModel());
    }
}
